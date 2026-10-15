# 计算流程连接规范

`graph-spec.json` 用于表达框架图中模块之间的有向计算流程，不用于逐条列举大型患者网络内部的全部生物学边。

## 文件结构

```json
{
  "nodes": [
    {"id": "input", "label": "Input features"},
    {"id": "encoder", "label": "Graph encoder"},
    {"id": "classifier", "label": "Classifier"}
  ],
  "edges": [
    {"from": "input", "to": "encoder", "type": "flow"},
    {"from": "encoder", "to": "classifier", "type": "flow"}
  ],
  "constraints": {
    "required_edges": [
      {"from": "input", "to": "encoder", "type": "flow"}
    ],
    "forbidden_edges": [],
    "exact_incoming": {"classifier": ["encoder"]},
    "exact_outgoing": {"input": ["encoder"]},
    "acyclic_flow": true
  }
}
```

`nodes` 项的 `id` 必须唯一，`label` 仅供人查看。每条 `edges` 必须指向已声明节点；`type` 默认是 `flow`，也可以使用 `provenance` 表示来源注释连接。结构约束默认只统计 `flow` 边。

- `required_edges`：指定必须存在的有向连接。未写 `type` 时按 `flow` 处理。
- `forbidden_edges`：指定不能出现的有向连接。
- `exact_incoming`：对指定节点约束其全部 `flow` 前驱，列表顺序无关。
- `exact_outgoing`：对指定节点约束其全部 `flow` 后继，列表顺序无关。
- `acyclic_flow`：设为 `true` 时，要求模块级 `flow` 连接无环。若研究流程本身含迭代或反馈环，设为 `false`，并另行说明循环边。

建议只把对理解模型有用的模块级流程放入规范，不要把装饰性布局线、图标内部边或一般性图例线作为模块连线。示意图中的生物学关系可以另用 `provenance` 注记，避免与计算步骤混淆。

## 运行

在该 skill 文件夹执行：

```text
python scripts/validate_graph.py path/to/graph-spec.json
```

退出码为 `0` 表示文件满足已声明的结构约束；非零退出码表示 JSON、节点、边或约束存在问题。通过校验不代表模型规范本身正确，作者和绘图者仍需与确认过的方法逐项对照。
