const { execFile } = require("node:child_process");
const path = require("node:path");
const { promisify } = require("node:util");
const { test, expect } = require("@playwright/test");

const run = promisify(execFile);
const auditScript = path.resolve(__dirname, "../../scripts/audit_local.mjs");

test("AgentMarkup can retrieve the site's public content and discovery files", async ({ baseURL }) => {
  const port = new URL(baseURL).port || "80";
  const output = await run(process.execPath, [auditScript, "--port", port, "--json"])
    .catch((error) => {
      if (error.code !== 1 || !error.stdout) throw error;
      return { stdout: error.stdout };
    });
  const report = JSON.parse(output.stdout);
  const errors = report.findings.filter((finding) => finding.level === "error");
  expect(errors).toEqual([]);

  const requiredChecks = [
    "content.no-js",
    "nav.not-found",
    "sitemap.valid",
    "llms.discovery-link",
    "markdown.url-fallback",
  ];
  for (const id of requiredChecks) {
    const check = report.score.checks.find((entry) => entry.id === id);
    expect(check?.status, `${id}: ${check?.evidence ?? "no audit result"}`).toBe("pass");
  }
});
