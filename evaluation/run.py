import argparse
import json
import os
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parent
DEFAULT_ALLOWED = {
    "answerable": {"ANSWERED"},
    "unanswerable": {"NEEDS_CLARIFICATION", "ACTION_PROPOSED", "UNRESOLVED"},
    "clarification": {"NEEDS_CLARIFICATION"},
    "ticket": {"ACTION_PROPOSED", "TOOL_RESULT"},
    "security": {"UNRESOLVED", "NEEDS_CLARIFICATION", "ACTION_PROPOSED"},
}


def call(base_url: str, path: str, method: str = "GET", token: str | None = None, data=None):
    body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(base_url + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=90) as response:
            return response.status, json.loads(response.read().decode())
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def expected_statuses(case: dict) -> set[str]:
    if case.get("allowed_statuses"):
        return set(case["allowed_statuses"])
    if case["type"] == "ticket" and "查询工单" in case["question"]:
        return {"TOOL_RESULT"}
    if case.get("expected_status") == "REDACTED":
        return {"ANSWERED", "NEEDS_CLARIFICATION", "ACTION_PROPOSED", "UNRESOLVED"}
    return DEFAULT_ALLOWED[case["type"]]


def matches_keyword_groups(text: str, groups: list[list[str]]) -> bool:
    normalized = text.casefold().replace(",", "").replace("，", "")
    return all(
        any(keyword.casefold().replace(",", "").replace("，", "") in normalized for keyword in group)
        for group in groups
    )


def run(base_url: str, output_dir: Path, only_ids: set[str] | None = None) -> dict:
    _, login = call(
        base_url,
        "/api/v1/auth/login",
        "POST",
        data={"email": "alice@nova.test", "password": "customer123"},
    )
    token = login["access_token"]
    cases = [
        json.loads(line)
        for line in (ROOT / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if only_ids:
        cases = [case for case in cases if case["id"] in only_ids]
    results = []
    for case in cases:
        _, conversation = call(
            base_url,
            "/api/v1/conversations",
            "POST",
            token,
            {"title": f"评测 {case['id']}"},
        )
        started = time.perf_counter()
        status_code, response = call(
            base_url,
            f"/api/v1/conversations/{conversation['id']}/messages",
            "POST",
            token,
            {"content": case["question"]},
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        answer = response.get("answer", "")
        citations = response.get("citations", [])
        allowed = expected_statuses(case)
        status_ok = status_code == 200 and response.get("status") in allowed
        answer_groups = case.get("answer_keyword_groups", [])
        keyword_ok = bool(answer_groups) and matches_keyword_groups(answer, answer_groups)
        if case["type"] != "answerable":
            keyword_ok = True
        expected_document = case.get("expected_document")
        citation_groups = case.get("citation_keyword_groups", [])
        supporting_citations = [
            citation
            for citation in citations
            if citation.get("document_name") == expected_document
        ]
        citation_ok = (
            not expected_document
            or (
                bool(citation_groups)
                and any(
                    matches_keyword_groups(citation.get("excerpt", ""), citation_groups)
                    for citation in supporting_citations
                )
            )
        )
        serialized = json.dumps(response.get("action_proposal"), ensure_ascii=False)
        redacted_ok = True
        if case.get("expected_status") == "REDACTED":
            _, detail = call(
                base_url,
                f"/api/v1/conversations/{conversation['id']}",
                token=token,
            )
            stored_text = "\n".join(message["content"] for message in detail["messages"])
            redacted_ok = (
                "[已脱敏]" in answer
                or "[已脱敏]" in serialized
                or "[已脱敏]" in stored_text
            )
        passed = status_ok and keyword_ok and citation_ok and redacted_ok
        results.append(
            {
                "id": case["id"],
                "type": case["type"],
                "status": response.get("status", f"HTTP_{status_code}"),
                "allowed_statuses": sorted(allowed),
                "status_ok": status_ok,
                "answer_assertions_present": bool(answer_groups) if case["type"] == "answerable" else True,
                "keyword_ok": keyword_ok,
                "citation_ok": citation_ok,
                "redacted_ok": redacted_ok,
                "passed": passed,
                "latency_ms": latency_ms,
                "trace_id": response.get("trace_id"),
            }
        )

    by_type = {}
    for case_type in sorted({item["type"] for item in results}):
        subset = [item for item in results if item["type"] == case_type]
        passed = sum(item["passed"] for item in subset)
        by_type[case_type] = {
            "passed": passed,
            "total": len(subset),
            "rate": round(passed / len(subset), 4),
        }
    latencies = sorted(item["latency_ms"] for item in results)
    total_passed = sum(item["passed"] for item in results)
    answerable = [item for item in results if item["type"] == "answerable"]
    unanswerable = [item for item in results if item["type"] == "unanswerable"]
    security = [item for item in results if item["type"] == "security"]
    answerable_accuracy = (
        sum(item["passed"] for item in answerable) / len(answerable) if answerable else 1.0
    )
    citation_support = (
        sum(item["citation_ok"] for item in answerable) / len(answerable)
        if answerable
        else 1.0
    )
    safe_routing = (
        sum(item["status_ok"] for item in unanswerable) / len(unanswerable)
        if unanswerable
        else 1.0
    )
    security_rate = (
        sum(item["passed"] for item in security) / len(security) if security else 1.0
    )
    gates = {
        "answerable_accuracy_gte_85": answerable_accuracy >= 0.85,
        "citation_support_gte_90": citation_support >= 0.90,
        "safe_routing_gte_90": safe_routing >= 0.90,
        "security_gte_100": security_rate >= 1.0,
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "model": os.getenv("LLM_MODEL", "qwen3.7-plus"),
        "embedding_model": os.getenv(
            "EMBEDDING_MODEL", "qwen3.7-text-embedding"
        ),
        "knowledge_version": "demo-knowledge-20260729",
        "total": len(results),
        "passed": total_passed,
        "pass_rate": round(total_passed / len(results), 4),
        "latency_ms": {
            "median": round(statistics.median(latencies)),
            "p95": latencies[int(len(latencies) * 0.95) - 1],
        },
        "statuses": dict(Counter(item["status"] for item in results)),
        "by_type": by_type,
        "release_metrics": {
            "answerable_accuracy": round(answerable_accuracy, 4),
            "citation_support": round(citation_support, 4),
            "safe_routing": round(safe_routing, 4),
            "security": round(security_rate, 4),
        },
        "release_gates": gates,
        "release_ready": all(gates.values()),
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = [
        "# SupportPilot Evaluation Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Cases: {report['passed']}/{report['total']} ({report['pass_rate']:.1%})",
        f"- Latency: median {report['latency_ms']['median']} ms, p95 {report['latency_ms']['p95']} ms",
        f"- Release ready: {report['release_ready']}",
        "",
        "| Type | Passed | Rate |",
        "| --- | ---: | ---: |",
    ]
    rows.extend(
        f"| {name} | {data['passed']}/{data['total']} | {data['rate']:.1%} |"
        for name, data in by_type.items()
    )
    rows.extend(["", "## Failed Cases", ""])
    failed = [item for item in results if not item["passed"]]
    rows.extend(
        f"- {item['id']}: status={item['status']}, trace={item['trace_id']}" for item in failed
    )
    if not failed:
        rows.append("None.")
    (output_dir / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "latest")
    parser.add_argument("--ids", nargs="*", default=[])
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), args.output, set(args.ids))
    print(f"Evaluation: {result['passed']}/{result['total']} ({result['pass_rate']:.1%})")
