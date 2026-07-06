import unittest
from pathlib import Path


class PrivatePanelDeployArtifactsTests(unittest.TestCase):
    def test_compose_uses_internal_network_without_public_ports(self):
        compose = Path("deploy/private-panel/docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("context: ../..", compose)
        self.assertIn("dockerfile: Dockerfile", compose)
        self.assertIn("env_file:", compose)
        self.assertIn("- .env", compose)
        self.assertIn("DOUK_PANEL_MODE=1", compose)
        self.assertIn("DOUK_PANEL_HOST=0.0.0.0", compose)
        self.assertIn("DOUK_PANEL_PORT=5555", compose)
        self.assertIn("DOUK_PANEL_VOLUME=/app/Volume", compose)
        self.assertIn("oceverse_halo_network", compose)
        self.assertIn("external: true", compose)
        self.assertIn("expose:", compose)
        self.assertIn('- "5555"', compose)
        self.assertIn("douk_private_panel_volume:/app/Volume", compose)
        self.assertNotIn("ports:", compose)

    def test_env_example_names_private_token_without_secret_value(self):
        env_text = Path("deploy/private-panel/env.example").read_text(encoding="utf-8")

        self.assertIn("DOUK_PRIVATE_TOKEN=", env_text)
        self.assertNotIn("secret", env_text.lower())
        self.assertIn("DOUK_PANEL_VOLUME=/app/Volume", env_text)

    def test_readme_documents_navi_gated_caddy_route(self):
        readme = Path("deploy/private-panel/README.md").read_text(encoding="utf-8")

        self.assertIn("/downloads", readme)
        self.assertIn("forward_auth", readme)
        self.assertIn("navi-save:8099", readme)
        self.assertIn("request_header @downloads_gated -X-Tradedocs-User-Id", readme)
        self.assertIn("request_header @downloads_gated -X-Tradedocs-User-Email", readme)
        self.assertIn("request_header @downloads_gated -X-Tradedocs-User-Name", readme)
        self.assertIn(
            "copy_headers X-Tradedocs-User-Id X-Tradedocs-User-Email X-Tradedocs-User-Name",
            readme,
        )
        self.assertIn("reverse_proxy douk-private-panel:5555", readme)
        self.assertIn("Do not publish a host port", readme)


if __name__ == "__main__":
    unittest.main()
