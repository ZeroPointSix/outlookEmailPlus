"""失效 Token 治理手动入口的前端回归测试。"""

import unittest
from pathlib import Path


class InvalidTokenGovernanceFrontendContractTests(unittest.TestCase):
    def test_manual_governance_loader_reveals_action_summary(self):
        """手动加载到候选后必须显示包含治理按钮的摘要区。"""
        repo_root = Path(__file__).resolve().parents[1]
        main_js = (repo_root / "static" / "js" / "main.js").read_text(encoding="utf-8")
        loader_start = main_js.index("async function loadInvalidTokenGovernanceCandidates")
        loader_end = main_js.index("/** 批量将失效 Token 候选账号置为停用 */", loader_start)
        loader_source = main_js[loader_start:loader_end]

        self.assertIn(
            "showInvalidTokenDetectionSummary(count, invalidTokenGovernanceCandidates);",
            loader_source,
            "手动失效治理入口加载到候选后没有显示治理操作区",
        )


if __name__ == "__main__":
    unittest.main()
