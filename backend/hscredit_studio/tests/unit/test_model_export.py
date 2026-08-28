"""模型导出单元测试 — Phase 7 B34."""
from __future__ import annotations

import pickle
from unittest.mock import MagicMock

import pytest

from hscredit_studio.schemas.model_export import (
    DemoModelRequest,
    ModelExportRequest,
    ModelFormat,
    ModelValidationRequest,
)
from hscredit_studio.services.model_export import (
    ModelType,
    ValidationResult,
    decode_model_bytes,
    encode_model_bytes,
    export_to_onnx,
    export_to_pmml,
    render_pmml_scorecard,
    validate_export,
)

# ===== Module-level fixtures (must be picklable) =====


class _PicklableModel:
    """可 pickle 的最小 sklearn-兼容模型 (用于校验测试)."""

    def __init__(self) -> None:
        self.coef_ = [[0.5]]
        self.intercept_ = [0.0]

    def predict_proba(self, x):
        return [[0.9, 0.1] for _ in x]

    def predict(self, x):
        return [0.1 for _ in x]


# ===== A. PMML 渲染 =====


class TestPMMLRendering:
    """PMML 渲染测试 (B34 验收)."""

    def test_render_pmml_scorecard_minimal(self) -> None:
        pmml = render_pmml_scorecard(
            feature_names=["age", "income", "credit_score"],
            coefficients=[0.05, 0.0001, 0.02],
            intercept=-3.5,
        )
        assert isinstance(pmml, bytes)
        content = pmml.decode("utf-8")
        assert "<?xml" in content
        assert "PMML" in content
        assert "version=\"4.4\"" in content

    def test_pmml_contains_features(self) -> None:
        pmml = render_pmml_scorecard(
            feature_names=["f1", "f2"],
            coefficients=[0.1, 0.2],
            intercept=0.5,
        ).decode("utf-8")
        assert "f1" in pmml
        assert "f2" in pmml
        assert "0.1" in pmml
        assert "0.2" in pmml
        assert "0.5" in pmml

    def test_pmml_regression_model(self) -> None:
        pmml = render_pmml_scorecard(
            feature_names=["x"],
            coefficients=[1.0],
            intercept=0.0,
        ).decode("utf-8")
        assert "RegressionModel" in pmml
        assert "RegressionTable" in pmml
        assert "NumericPredictor" in pmml

    def test_pmml_data_dictionary(self) -> None:
        pmml = render_pmml_scorecard(
            feature_names=["a", "b", "c"],
            coefficients=[1.0, 2.0, 3.0],
            intercept=0.0,
        ).decode("utf-8")
        assert "DataDictionary" in pmml
        assert 'numberOfFields="3"' in pmml


# ===== B. PMML 导出 (含 sklearn 适配) =====


class TestPMMLExport:
    """PMML 导出测试."""

    def test_export_scorecard_to_pmml(self) -> None:
        model = {
            "name": "TestScorecard",
            "coefficients": [0.1, 0.2, 0.3],
            "intercept": -2.0,
        }
        result = export_to_pmml(
            model=model,
            feature_names=["a", "b", "c"],
            model_type=ModelType.SCORECARD,
        )
        assert result.format == ModelFormat.PMML
        assert result.mime_type == "application/pmml+xml"
        assert result.filename.endswith(".pmml")
        assert len(result.bytes_content) > 0
        assert b"PMML" in result.bytes_content

    def test_export_sklearn_fallback(self) -> None:
        """sklearn 无 sklearn2pmml 时, 手工 PMML 渲染."""
        # 用 mock 模拟 sklearn 模型
        mock_model = MagicMock()
        mock_model.coef_ = [[0.5, 0.3, 0.2]]
        mock_model.intercept_ = [-1.0]

        result = export_to_pmml(
            model=mock_model,
            feature_names=["x", "y", "z"],
            model_type=ModelType.SKLEARN,
        )
        assert result.format == ModelFormat.PMML
        # 无 sklearn2pmml 时, 一定有 warning
        assert any("sklearn2pmml" in w or "手工" in w for w in result.warnings)

    def test_export_unsupported_model_warning(self) -> None:
        """不支持的模型类型给出 warning."""
        result = export_to_pmml(
            model=MagicMock(),
            feature_names=["x"],
            model_type=ModelType.LIGHTGBM,
        )
        assert any("暂不支持" in w or "Unsupported" in w for w in result.warnings)


# ===== C. ONNX 导出 =====


class TestONNXExport:
    """ONNX 导出测试."""

    def test_export_sklearn_onnx_fallback(self) -> None:
        mock_model = MagicMock()
        mock_model.coef_ = [[0.5, 0.3]]
        mock_model.intercept_ = [-1.0]

        result = export_to_onnx(
            model=mock_model,
            feature_names=["x", "y"],
            model_type=ModelType.SKLEARN,
        )
        assert result.format == ModelFormat.ONNX
        assert result.mime_type == "application/onnx"
        assert result.filename.endswith(".onnx")
        assert any("skl2onnx" in w or "手工" in w or "最小" in w for w in result.warnings)

    def test_export_scorecard_onnx(self) -> None:
        model = {"coefficients": [0.1, 0.2], "intercept": 0.0}
        result = export_to_onnx(
            model=model,
            feature_names=["a", "b"],
            model_type=ModelType.SCORECARD,
        )
        assert result.format == ModelFormat.ONNX
        assert len(result.bytes_content) > 0

    def test_export_onnx_unsupported_model_warning(self) -> None:
        result = export_to_onnx(
            model=MagicMock(),
            feature_names=["x"],
            model_type=ModelType.XGBOOST,
        )
        assert any("暂不支持" in w for w in result.warnings)


# ===== D. 校验 =====


class TestValidation:
    """导出校验测试 (B34 验收 — 跨平台一致性)."""

    def test_validate_sklearn_consistency(self) -> None:
        """同一模型 pickle 后预测应一致."""
        model = _PicklableModel()
        exported_bytes = pickle.dumps(model)

        result = validate_export(
            original_model=model,
            exported_format=ModelFormat.PMML,
            exported_bytes=exported_bytes,
            sample_inputs=[[1.0], [2.0], [3.0]],
            tolerance=1e-6,
        )
        assert result.passed is True
        assert result.sample_count == 3
        assert result.max_abs_error == 0.0  # 完全相同

    def test_validate_no_samples(self) -> None:
        mock_model = MagicMock()
        result = validate_export(
            original_model=mock_model,
            exported_format=ModelFormat.PMML,
            exported_bytes=b"",
            sample_inputs=[],
        )
        assert result.passed is False
        assert "无样本" in result.message

    def test_validate_original_fails(self) -> None:
        mock_model = MagicMock(spec=[])  # 无 predict
        result = validate_export(
            original_model=mock_model,
            exported_format=ModelFormat.PMML,
            exported_bytes=b"",
            sample_inputs=[[1.0]],
        )
        assert result.passed is False
        assert "失败" in result.message

    def test_validation_result_fields(self) -> None:
        """ValidationResult 字段完整性."""
        r = ValidationResult(
            passed=True,
            max_abs_error=1e-9,
            mean_abs_error=5e-10,
            sample_count=10,
            original_predictions=[0.1, 0.2],
            exported_predictions=[0.1, 0.2],
            message="通过",
        )
        assert r.passed
        assert r.sample_count == 10
        assert "通过" in r.message


# ===== E. Base64 编解码 =====


class TestBase64Codec:
    """Base64 编解码."""

    def test_encode_decode_roundtrip(self) -> None:
        original = b"hello world \x00\x01\x02"
        encoded = encode_model_bytes(original)
        assert isinstance(encoded, str)
        decoded = decode_model_bytes(encoded)
        assert decoded == original

    def test_encode_empty(self) -> None:
        assert encode_model_bytes(b"") == ""
        assert decode_model_bytes("") == b""


# ===== F. schemas 校验 =====


class TestSchemas:
    """B34 Schemas Pydantic 校验."""

    def test_export_request_min_features(self) -> None:

        with pytest.raises(ValueError):
            ModelExportRequest(
                model_b64="YWJj",
                model_type=ModelType.SKLEARN,
                feature_names=[],  # 空, 应报错
                format=ModelFormat.PMML,
            )

    def test_export_request_happy(self) -> None:
        req = ModelExportRequest(
            model_b64="YWJj",
            model_type=ModelType.SKLEARN,
            feature_names=["x"],
            format=ModelFormat.ONNX,
        )
        assert req.format == ModelFormat.ONNX

    def test_validation_request_tolerance_bounds(self) -> None:
        with pytest.raises(ValueError):
            ModelValidationRequest(
                original_model_b64="YWJj",
                exported_format=ModelFormat.PMML,
                exported_content_b64="YWJj",
                sample_inputs=[[1.0]],
                tolerance=2.0,  # 超出 1.0 上限
            )

    def test_demo_request_default(self) -> None:
        req = DemoModelRequest()
        assert len(req.feature_names) >= 1
