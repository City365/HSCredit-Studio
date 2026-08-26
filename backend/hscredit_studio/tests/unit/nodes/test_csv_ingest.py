"""CSV 接入节点 smoke test."""
import pytest
import tempfile
import os
import pandas as pd
from hscredit_studio.nodes.data_ingest.csv_ingest import CSVIngestNode


@pytest.fixture
def sample_csv():
    """创建临时 CSV 文件."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("id,name,score\n")
        f.write("1,Alice,0.85\n")
        f.write("2,Bob,0.92\n")
        f.write("3,Charlie,0.78\n")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_csv_ingest_basic(sample_csv):
    node = CSVIngestNode()
    outputs = node.run(inputs={}, params={"path": sample_csv, "sep": ",", "encoding": "utf-8"})
    df = outputs["df"]
    schema = outputs["schema"]
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    assert list(df.columns) == ["id", "name", "score"]
    assert schema["id"] in ("int64", "int32")
    assert schema["name"] == "object"


def test_csv_ingest_missing_path():
    node = CSVIngestNode()
    with pytest.raises(Exception):  # ValidationError
        node.run(inputs={}, params={"path": ""})


def test_csv_ingest_nonexistent_file():
    node = CSVIngestNode()
    with pytest.raises(Exception):
        node.run(inputs={}, params={"path": "/tmp/this_file_does_not_exist_12345.csv"})


def test_csv_ingest_validate_params():
    node = CSVIngestNode()
    params = node.contract.params
    assert any(p.name == "path" and p.required for p in params)
    assert any(p.name == "sep" and not p.required for p in params)


def test_csv_ingest_contract_metadata():
    node = CSVIngestNode()
    assert node.contract.node_type == "csv_ingest"
    assert node.contract.category.value == "数据接入"
    assert "DataFrame" in {p.type for p in node.contract.outputs}


def test_csv_ingest_with_nrows_limit(sample_csv):
    """nrows 参数应限制读取行数."""
    node = CSVIngestNode()
    outputs = node.run(inputs={}, params={"path": sample_csv, "nrows": 2})
    df = outputs["df"]
    assert len(df) == 2