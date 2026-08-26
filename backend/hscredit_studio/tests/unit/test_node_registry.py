"""单元测试 — NodeRegistry."""
import pytest
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import NodeRegistry, register_node
from hscredit_studio.schemas.node_contract import NodeContract, NodeCategory, PortSchema, ParamSpec, CacheConfig
from hscredit_studio.core.exceptions import NodeNotFoundError


@pytest.fixture(autouse=True)
def clean_registry():
    """每个测试前后清空注册表."""
    NodeRegistry.clear()
    yield
    NodeRegistry.clear()


def test_register_node():
    @register_node
    class TestNode(BaseNode):
        contract = NodeContract(
            node_type="test_node",
            category=NodeCategory("数据接入"),
            name="Test",
            description="test node",
        )
        def run(self, inputs, params):
            return {}

    assert NodeRegistry.count() == 1
    node_cls = NodeRegistry.get("test_node")
    assert node_cls is TestNode


def test_register_duplicate_raises():
    @register_node
    class TestNode(BaseNode):
        contract = NodeContract(
            node_type="test_dup",
            category=NodeCategory("数据接入"),
            name="Test",
            description="",
        )
        def run(self, inputs, params): return {}

    with pytest.raises(ValueError, match="已被"):
        @register_node
        class AnotherTestNode(BaseNode):
            contract = NodeContract(
                node_type="test_dup",
                category=NodeCategory("数据接入"),
                name="Test2",
                description="",
            )
            def run(self, inputs, params): return {}


def test_get_nonexistent_node():
    with pytest.raises(NodeNotFoundError):
        NodeRegistry.get("nonexistent")


def test_try_get_returns_none_for_missing():
    assert NodeRegistry.try_get("nonexistent") is None


def test_list_by_category():
    @register_node
    class DataIngest(BaseNode):
        contract = NodeContract(
            node_type="data_1",
            category=NodeCategory("数据接入"),
            name="Data1",
            description="",
        )
        def run(self, inputs, params): return {}

    @register_node
    class Model(BaseNode):
        contract = NodeContract(
            node_type="model_1",
            category=NodeCategory("模型训练"),
            name="Model1",
            description="",
        )
        def run(self, inputs, params): return {}

    data_nodes = NodeRegistry.list_by_category(NodeCategory("数据接入"))
    assert len(data_nodes) == 1
    assert data_nodes[0].contract.node_type == "data_1"


def test_list_contracts():
    @register_node
    class TestNode(BaseNode):
        contract = NodeContract(
            node_type="test_a",
            category=NodeCategory("数据接入"),
            name="A",
            description="",
        )
        def run(self, inputs, params): return {}

    contracts = NodeRegistry.list_contracts()
    assert len(contracts) == 1
    assert contracts[0].node_type == "test_a"


def test_register_node_with_all_7_categories():
    """所有 7 个分类都能注册."""
    categories = ["数据接入", "EDA", "特征工程", "特征筛选", "模型训练", "评分卡与规则", "报告与部署"]
    for i, cat in enumerate(categories):
        @register_node
        class N(BaseNode):
            contract = NodeContract(
                node_type=f"node_{i}",
                category=NodeCategory(cat),
                name=f"Node {i}",
                description="",
            )
            def run(self, inputs, params): return {}

    assert NodeRegistry.count() == 7


def test_register_node_without_contract_raises():
    """缺少 contract 类变量应抛 ValueError."""
    with pytest.raises(ValueError, match="contract"):
        NodeRegistry.register(type("NoContract", (BaseNode,), {}))


def test_unregister_node():
    @register_node
    class TmpNode(BaseNode):
        contract = NodeContract(
            node_type="tmp_node",
            category=NodeCategory("EDA"),
            name="Tmp",
            description="",
        )
        def run(self, inputs, params): return {}

    assert NodeRegistry.count() == 1
    NodeRegistry.unregister("tmp_node")
    assert NodeRegistry.count() == 0
    assert NodeRegistry.try_get("tmp_node") is None


def test_unregister_nonexistent_is_noop():
    """注销不存在的节点是空操作（幂等）."""
    NodeRegistry.unregister("never_existed")
    assert NodeRegistry.count() == 0


def test_list_all_returns_all_registered():
    @register_node
    class A(BaseNode):
        contract = NodeContract(node_type="a", category=NodeCategory("EDA"), name="A", description="")
        def run(self, inputs, params): return {}

    @register_node
    class B(BaseNode):
        contract = NodeContract(node_type="b", category=NodeCategory("EDA"), name="B", description="")
        def run(self, inputs, params): return {}

    all_nodes = NodeRegistry.list_all()
    assert len(all_nodes) == 2
    types = {n.contract.node_type for n in all_nodes}
    assert types == {"a", "b"}