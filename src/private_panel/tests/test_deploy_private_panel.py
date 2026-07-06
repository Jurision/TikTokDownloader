import unittest
from pathlib import Path


class PrivatePanelDeployArtifactsTests(unittest.TestCase):
    def test_compose_uses_internal_network_without_public_ports(self):
        compose = Path("deploy/private-panel/docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("douk-private-panel:", compose)
        self.assertIn("container_name: douk-private-panel", compose)
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
        self.assertNotIn("network_mode:", compose)
        self.assertNotIn("network_mode: host", compose)

    def test_env_example_names_private_token_without_secret_value(self):
        env_text = Path("deploy/private-panel/env.example").read_text(encoding="utf-8")
        env_values = dict(
            line.split("=", 1)
            for line in env_text.splitlines()
            if line and not line.startswith("#")
        )

        self.assertEqual(env_values["DOUK_PRIVATE_TOKEN"], "")
        self.assertEqual(env_values["DOUK_ALLOWED_NAVI_USER_IDS"], "")
        self.assertEqual(env_values["DOUK_ALLOWED_NAVI_USER_EMAILS"], "")
        self.assertEqual(env_values["DOUK_TRUSTED_PROXY_SECRET"], "")
        self.assertEqual(env_values["DOUK_PANEL_VOLUME"], "/app/Volume")

    def test_readme_documents_navi_gated_caddy_route(self):
        readme = Path("deploy/private-panel/README.md").read_text(encoding="utf-8")

        self.assertIn("/downloads", readme)
        self.assertIn("forward_auth", readme)
        self.assertIn("navi-save:8099", readme)
        self.assertIn("route @downloads_gated {", readme)
        self.assertIn("request_header -X-Tradedocs-User-Id", readme)
        self.assertIn("request_header -X-Tradedocs-User-Email", readme)
        self.assertIn("request_header -X-Tradedocs-User-Name", readme)
        self.assertIn("request_header -X-Douk-Trusted-Proxy", readme)
        self.assertIn("request_header -Authorization", readme)
        self.assertIn("request_header -X-Douk-Token", readme)
        self.assertIn(
            "copy_headers X-Tradedocs-User-Id X-Tradedocs-User-Email X-Tradedocs-User-Name",
            readme,
        )
        self.assertIn("X-Douk-Trusted-Proxy", readme)
        self.assertIn("DOUK_ALLOWED_NAVI_USER_IDS", readme)
        self.assertIn("DOUK_ALLOWED_NAVI_USER_EMAILS", readme)
        self.assertIn("redir /downloads /downloads/ 308", readme)
        self.assertIn("reverse_proxy /downloads/* douk-private-panel:5555", readme)
        self.assertIn("cp deploy/private-panel/env.example deploy/private-panel/.env", readme)
        self.assertIn("chmod 600 deploy/private-panel/.env", readme)
        self.assertIn("docker compose -f deploy/private-panel/docker-compose.yml config --quiet", readme)
        self.assertIn("docker compose -f deploy/private-panel/docker-compose.yml down", readme)
        self.assertIn("Do not publish a host port", readme)
        self.assertLess(
            readme.index("request_header -X-Tradedocs-User-Id"),
            readme.index("forward_auth @downloads_gated navi-save:8099"),
        )
        self.assertLess(
            readme.index("forward_auth @downloads_gated navi-save:8099"),
            readme.index("reverse_proxy /downloads/* douk-private-panel:5555"),
        )

    def test_readme_documents_supported_douyin_job_modes(self):
        readme = Path("deploy/private-panel/README.md").read_text(encoding="utf-8")

        self.assertIn("douyin_single", readme)
        self.assertIn("douyin_account_posts", readme)
        self.assertIn("douyin_account_liked", readme)
        self.assertIn("douyin_favorites", readme)
        self.assertIn("douyin_mix", readme)
        self.assertIn("owner_url.url", readme)
        self.assertIn("accounts_urls", readme)
        self.assertIn("mix_urls", readme)

    def test_local_env_file_is_ignored_by_git_and_docker_build_context(self):
        gitignore = Path(".gitignore").read_text(encoding="utf-8")
        dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

        self.assertIn("/deploy/private-panel/.env", gitignore)
        self.assertIn("deploy/private-panel/.env", dockerignore)


if __name__ == "__main__":
    unittest.main()
