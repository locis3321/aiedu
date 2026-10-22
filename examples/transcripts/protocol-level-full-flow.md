# 协议级真实完整流程记录（教学编排：16-9 破十法五关）

> 由真实 MCP 调用（MCP 官方 Python client ↔ aiedu_mcp.server stdio）逐条生成，无模拟。
> 学生答案由记录者扮演，每关一条真实 `submit_attempt`；其中第 2 关故意答错一次以演示提示阶梯。
> 对照三端 Agent 会话转录使用。

### ① generate_lesson('16-9') → 信封（spec 本体在 spec 字段）
```json
{
  "lesson_id": "borrow-ten-16-minus-9",
  "spec": {
    "schema_version": "2.0",
    "lesson_id": "borrow-ten-16-minus-9",
    "revision": 1,
    "teaching_request": {
      "kind": "problem",
      "content": "16-9"
    },
    "curriculum_context": {
      "stage": "primary",
      "grade": 2
    },
    "learning_objectives": [
      {
        "id": "lo-borrow-ten",
        "description": "用破十法计算16-9"
      }
    ],
    "domain_models": [
      {
        "id": "m-arithmetic",
        "domain": "arithmetic",
        "plugin_version": "0.1.0"
      }
    ],
    "teaching_design": {
      "modes": [
        "引导"
      ],
      "strategy_refs": [
        "borrow_ten@0.1.0"
      ],
      "skill_refs": [
        "borrow-ten"
      ]
    },
    "verification": {
      "verified": true,
      "verifier_version": "0.1.0",
      "normalized_problem_hash": null,
      "assumptions": [],
      "claims": [
        {
          "id": "arithmetic",
          "statement": "16-9=7（破十：(10-9)+(16-10)=1+6=7）",
          "status": "verified",
          "method": "精确计算"
        }
      ],
      "covered_claim_ids": [
        "arithmetic"
      ],
      "report_ref": null,
      "mode": "math_verified_applicable"
    },
    "initial_states": {
      "m-arithmetic": {
        "tens": 1,
        "ones": 6,
        "borrowed": 0
      }
    },
    "operations": [
      {
        "id": "arithmetic.break_ten"
      },
      {
        "id": "arithmetic.recombine"
      }
    ],
    "activity_graph": [
      {
        "id": "find-tens",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "borrow-ten"
        ],
        "prompt": "小松鼠有 16 颗松果，每 10 颗装成一捆。零散着（不够一捆）的有几颗？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "6"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "把 16 分成十位和个位：十位是 1，个位是 6。"
        ],
        "on_correct": [],
        "on_incorrect": null
      },
      {
        "id": "borrow-ten",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "subtract-rest"
        ],
        "prompt": "要送朋友 9 颗，但零散的 6 颗不够。小松鼠解开一捆（10 颗）。10 - 9 = ?",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "1"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "一捆有 10 颗，从这 10 颗里拿 9 颗送人。"
        ],
        "on_correct": [
          "arithmetic.break_ten"
        ],
        "on_incorrect": null
      },
      {
        "id": "subtract-rest",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "merge"
        ],
        "prompt": "解开一捆后，原来的 16 颗还剩多少颗（整捆和零散一起算）？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "6"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "原来有 1 捆，解开 1 捆后还剩 0 捆，再加零散的 6 颗。"
        ],
        "on_correct": [],
        "on_incorrect": null
      },
      {
        "id": "merge",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "replay"
        ],
        "prompt": "解开的这 10 颗里送走 9 颗后剩下 1 颗，把它和剩下的 6 颗合起来，一共是多少颗？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "7"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "10 里减掉 9 后剩 1 颗，再合上剩下的 6 颗。"
        ],
        "on_correct": [
          "arithmetic.recombine"
        ],
        "on_incorrect": null
      },
      {
        "id": "replay",
        "type": "observe",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "transfer-practice"
        ],
        "narration": "完整演示：16 里个位 6 不够减 9，把 1 个十拆成 10 个一：10-9=1，剩下的 6 颗一起算：1+6=7。这就是破十法——个位不够减时，从十位借 1 个十拆成 10 个一，先减再加，总量不变。"
      },
      {
        "id": "transfer-practice",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "__end__"
        ],
        "prompt": "试试这题：10-1怎么算？（先自己想一想）",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "9"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "个位够不够减？不够就从十位借 1 个十。"
        ],
        "on_correct": [],
        "on_incorrect": null
      }
    ],
    "assessment": [
      {
        "id": "assess-diff",
        "objective_refs": [
          "lo-borrow-ten"
        ],
        "evidence_kind": "numeric_answer",
        "rubric_refs": []
      }
    ],
    "replay": null,
    "representations": [
      {
        "id": "rep-bundles",
        "model_refs": [
          "m-arithmetic"
        ],
        "kind": "diagram_2d",
        "adapter_version": null
      }
    ],
    "render": {
      "runtime_version": "0.1.0",
      "representation_adapter_versions": {},
      "asset_manifest_ref": null,
      "layout_strategy": "responsive"
    },
    "presentation": {
      "age_band": "lower_primary",
      "visual_theme": "storybook",
      "scene_metaphor": "pinecone_bundles",
      "feedback_tone": "encouraging",
      "motion_style": "playful",
      "interaction_affordances": [
        "type",
        "tap"
      ]
    }
  },
  "verification": {
    "verified": true,
    "verifier_version": "0.1.0",
    "normalized_problem_hash": null,
    "assumptions": [],
    "claims": [
      {
        "id": "arithmetic",
        "statement": "16-9=7（破十：(10-9)+(16-10)=1+6=7）",
        "status": "verified",
        "method": "精确计算"
      }
    ],
    "covered_claim_ids": [
      "arithmetic"
    ],
    "report_ref": null,
    "mode": "math_verified_applicable"
  }
}
```

### ② get_lesson(reveal='filtered')：未解锁节点 response.expected 均为 null（先想后看）
```json
{
  "spec": {
    "schema_version": "2.0",
    "lesson_id": "borrow-ten-16-minus-9",
    "revision": 1,
    "teaching_request": {
      "kind": "problem",
      "content": "16-9"
    },
    "curriculum_context": {
      "stage": "primary",
      "grade": 2
    },
    "learning_objectives": [
      {
        "id": "lo-borrow-ten",
        "description": "用破十法计算16-9"
      }
    ],
    "domain_models": [
      {
        "id": "m-arithmetic",
        "domain": "arithmetic",
        "plugin_version": "0.1.0"
      }
    ],
    "teaching_design": {
      "modes": [
        "引导"
      ],
      "strategy_refs": [
        "borrow_ten@0.1.0"
      ],
      "skill_refs": [
        "borrow-ten"
      ]
    },
    "verification": {
      "verified": true,
      "verifier_version": "0.1.0",
      "normalized_problem_hash": null,
      "assumptions": [],
      "claims": [
        {
          "id": "arithmetic",
          "statement": "",
          "status": "verified",
          "method": "精确计算"
        }
      ],
      "covered_claim_ids": [
        "arithmetic"
      ],
      "report_ref": null,
      "mode": "math_verified_applicable"
    },
    "initial_states": {
      "m-arithmetic": {
        "tens": 1,
        "ones": 6,
        "borrowed": 0
      }
    },
    "operations": [
      {
        "id": "arithmetic.break_ten"
      },
      {
        "id": "arithmetic.recombine"
      }
    ],
    "activity_graph": [
      {
        "id": "find-tens",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "borrow-ten"
        ],
        "prompt": "小松鼠有 16 颗松果，每 10 颗装成一捆。零散着（不够一捆）的有几颗？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": null,
          "correct_index": null
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "把 16 分成十位和个位：十位是 1，个位是 6。"
        ],
        "on_correct": [],
        "on_incorrect": null,
        "locked": true
      },
      {
        "id": "borrow-ten",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "subtract-rest"
        ],
        "prompt": "要送朋友 9 颗，但零散的 6 颗不够。小松鼠解开一捆（10 颗）。10 - 9 = ?",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": null,
          "correct_index": null
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "一捆有 10 颗，从这 10 颗里拿 9 颗送人。"
        ],
        "on_correct": [
          "arithmetic.break_ten"
        ],
        "on_incorrect": null,
        "locked": true
      },
      {
        "id": "subtract-rest",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "merge"
        ],
        "prompt": "解开一捆后，原来的 16 颗还剩多少颗（整捆和零散一起算）？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": null,
          "correct_index": null
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "原来有 1 捆，解开 1 捆后还剩 0 捆，再加零散的 6 颗。"
        ],
        "on_correct": [],
        "on_incorrect": null,
        "locked": true
      },
      {
        "id": "merge",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "replay"
        ],
        "prompt": "解开的这 10 颗里送走 9 颗后剩下 1 颗，把它和剩下的 6 颗合起来，一共是多少颗？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": null,
          "correct_index": null
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "10 里减掉 9 后剩 1 颗，再合上剩下的 6 颗。"
        ],
        "on_correct": [
          "arithmetic.recombine"
        ],
        "on_incorrect": null,
        "locked": true
      },
      {
        "id": "replay",
        "type": "observe",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "transfer-practice"
        ],
        "narration": "",
        "locked": true
      },
      {
        "id": "transfer-practice",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "__end__"
        ],
        "prompt": "试试这题：10-1怎么算？（先自己想一想）",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": null,
          "correct_index": null
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "个位够不够减？不够就从十位借 1 个十。"
        ],
        "on_correct": [],
        "on_incorrect": null,
        "locked": true
      }
    ],
    "assessment": [
      {
        "id": "assess-diff",
        "objective_refs": [
          "lo-borrow-ten"
        ],
        "evidence_kind": "numeric_answer",
        "rubric_refs": []
      }
    ],
    "representations": [
      {
        "id": "rep-bundles",
        "model_refs": [
          "m-arithmetic"
        ],
        "kind": "diagram_2d",
        "adapter_version": null
      }
    ],
    "render": {
      "runtime_version": "0.1.0",
      "representation_adapter_versions": {},
      "asset_manifest_ref": null,
      "layout_strategy": "responsive"
    },
    "presentation": {
      "age_band": "lower_primary",
      "visual_theme": "storybook",
      "scene_metaphor": "pinecone_bundles",
      "feedback_tone": "encouraging",
      "motion_style": "playful",
      "interaction_affordances": [
        "type",
        "tap"
      ]
    }
  },
  "reveal": "filtered"
}
```

### ③.2 submit_attempt(find-tens, 我答 6)
```json
{
  "correct": true,
  "evidence": "independent"
}
```

### ③.3 submit_attempt(borrow-ten, 我答 10)（答错 → evidence=assisted，取提示阶梯下一条）
```json
{
  "correct": false,
  "evidence": "assisted",
  "hint": "一捆有 10 颗，从这 10 颗里拿 9 颗送人。"
}
```

### ③.4 submit_attempt(borrow-ten, 我答 1)
```json
{
  "correct": true,
  "evidence": "independent"
}
```

### ③.5 submit_attempt(subtract-rest, 我答 6)
```json
{
  "correct": true,
  "evidence": "independent"
}
```

### ③.6 submit_attempt(merge, 我答 7)
```json
{
  "correct": true,
  "evidence": "independent"
}
```

### ③.7 submit_attempt(transfer-practice, 我答 9)
```json
{
  "correct": true,
  "evidence": "independent"
}
```

### ④ 全部达标 → get_lesson(reveal='full') 完整讲解（此刻才可见答案与回放）
```json
{
  "spec": {
    "schema_version": "2.0",
    "lesson_id": "borrow-ten-16-minus-9",
    "revision": 1,
    "teaching_request": {
      "kind": "problem",
      "content": "16-9"
    },
    "curriculum_context": {
      "stage": "primary",
      "grade": 2
    },
    "learning_objectives": [
      {
        "id": "lo-borrow-ten",
        "description": "用破十法计算16-9"
      }
    ],
    "domain_models": [
      {
        "id": "m-arithmetic",
        "domain": "arithmetic",
        "plugin_version": "0.1.0"
      }
    ],
    "teaching_design": {
      "modes": [
        "引导"
      ],
      "strategy_refs": [
        "borrow_ten@0.1.0"
      ],
      "skill_refs": [
        "borrow-ten"
      ]
    },
    "verification": {
      "verified": true,
      "verifier_version": "0.1.0",
      "normalized_problem_hash": null,
      "assumptions": [],
      "claims": [
        {
          "id": "arithmetic",
          "statement": "16-9=7（破十：(10-9)+(16-10)=1+6=7）",
          "status": "verified",
          "method": "精确计算"
        }
      ],
      "covered_claim_ids": [
        "arithmetic"
      ],
      "report_ref": null,
      "mode": "math_verified_applicable"
    },
    "initial_states": {
      "m-arithmetic": {
        "tens": 1,
        "ones": 6,
        "borrowed": 0
      }
    },
    "operations": [
      {
        "id": "arithmetic.break_ten"
      },
      {
        "id": "arithmetic.recombine"
      }
    ],
    "activity_graph": [
      {
        "id": "find-tens",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "borrow-ten"
        ],
        "prompt": "小松鼠有 16 颗松果，每 10 颗装成一捆。零散着（不够一捆）的有几颗？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "6"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "把 16 分成十位和个位：十位是 1，个位是 6。"
        ],
        "on_correct": [],
        "on_incorrect": null
      },
      {
        "id": "borrow-ten",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "subtract-rest"
        ],
        "prompt": "要送朋友 9 颗，但零散的 6 颗不够。小松鼠解开一捆（10 颗）。10 - 9 = ?",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "1"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "一捆有 10 颗，从这 10 颗里拿 9 颗送人。"
        ],
        "on_correct": [
          "arithmetic.break_ten"
        ],
        "on_incorrect": null
      },
      {
        "id": "subtract-rest",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "merge"
        ],
        "prompt": "解开一捆后，原来的 16 颗还剩多少颗（整捆和零散一起算）？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "6"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "原来有 1 捆，解开 1 捆后还剩 0 捆，再加零散的 6 颗。"
        ],
        "on_correct": [],
        "on_incorrect": null
      },
      {
        "id": "merge",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "replay"
        ],
        "prompt": "解开的这 10 颗里送走 9 颗后剩下 1 颗，把它和剩下的 6 颗合起来，一共是多少颗？",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "7"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "10 里减掉 9 后剩 1 颗，再合上剩下的 6 颗。"
        ],
        "on_correct": [
          "arithmetic.recombine"
        ],
        "on_incorrect": null
      },
      {
        "id": "replay",
        "type": "observe",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "transfer-practice"
        ],
        "narration": "完整演示：16 里个位 6 不够减 9，把 1 个十拆成 10 个一：10-9=1，剩下的 6 颗一起算：1+6=7。这就是破十法——个位不够减时，从十位借 1 个十拆成 10 个一，先减再加，总量不变。"
      },
      {
        "id": "transfer-practice",
        "type": "predict",
        "objective_refs": [],
        "model_refs": [],
        "representation_refs": [],
        "completion_refs": [],
        "next_ids": [
          "__end__"
        ],
        "prompt": "试试这题：10-1怎么算？（先自己想一想）",
        "response": {
          "kind": "number",
          "unit": null,
          "allow_expression": false,
          "expected": "9"
        },
        "gate": {
          "mode": "require_attempt",
          "max_assists": 3
        },
        "assistance": [
          "个位够不够减？不够就从十位借 1 个十。"
        ],
        "on_correct": [],
        "on_incorrect": null
      }
    ],
    "assessment": [
      {
        "id": "assess-diff",
        "objective_refs": [
          "lo-borrow-ten"
        ],
        "evidence_kind": "numeric_answer",
        "rubric_refs": []
      }
    ],
    "replay": null,
    "representations": [
      {
        "id": "rep-bundles",
        "model_refs": [
          "m-arithmetic"
        ],
        "kind": "diagram_2d",
        "adapter_version": null
      }
    ],
    "render": {
      "runtime_version": "0.1.0",
      "representation_adapter_versions": {},
      "asset_manifest_ref": null,
      "layout_strategy": "responsive"
    },
    "presentation": {
      "age_band": "lower_primary",
      "visual_theme": "storybook",
      "scene_metaphor": "pinecone_bundles",
      "feedback_tone": "encouraging",
      "motion_style": "playful",
      "interaction_affordances": [
        "type",
        "tap"
      ]
    }
  },
  "reveal": "full"
}
```

### ⑤ 收束抽查：verify_math('23-8', 15)（换数对确认不是背的）
```json
{
  "result": "verified",
  "verifier_version": "0.1.0",
  "claims": [
    {
      "id": "arithmetic-eq",
      "statement": "23-8 = 15.0",
      "status": "verified",
      "method": "精确计算"
    }
  ],
  "covered_claim_ids": [
    "arithmetic-eq"
  ]
}
```
