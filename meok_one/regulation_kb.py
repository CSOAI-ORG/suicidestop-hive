"""
MEOK ONE — REGULATION KB: authoritative grounding for compliance generation.

The moat unlock (2026-06-16). The verifier catches wrong citations; this makes the
model GET THEM RIGHT in the first place by injecting authoritative regulation context
into the prompt BEFORE generation. Ungrounded, a 3B (or even a frontier) model guesses
"Article 19"; grounded with "Article 50 governs transparency, applies 2 Aug 2026", it
cites correctly → the verifier passes it → a verified-CORRECT, audit-logged answer.

This curated KB is the SEED of what MEOK's ~271 compliance-MCP corpus serves at scale.
Facts are drawn from the regulations themselves (EU AI Act Reg. 2024/1689, DORA, NIS2).
Keep it correct — this is the ground truth the whole product leans on.

    ground(question) -> (context_string, matched_topics)   # inject before generation
"""
from __future__ import annotations

import re

# topic_key -> {triggers, article, title, date, obligation, framework}
# `article` is the citation the verifier (verifier.citation_correct) expects.
KB = {
    "transparency": {
        "triggers": r"transparen|watermark|ai[- ]?generated|deepfake|chatbot|synthetic (?:content|media)|disclos",
        "article": "Article 50", "framework": "EU AI Act (Reg. 2024/1689)",
        "title": "Transparency obligations for providers and deployers of certain AI systems",
        "date": "applies 2 December 2026 (delayed from 2 Aug 2026 by the Digital Omnibus, May 2026)",
        "obligation": "AI systems that interact with humans, or generate synthetic audio/image/"
                      "video/text, must disclose AI involvement and mark outputs as artificially "
                      "generated in a machine-readable way (deepfakes + AI text labelled).",
    },
    "high_risk": {
        "triggers": r"high[- ]?risk|credit[- ]?scor|annex\s*iii|biometric|recruitment|hiring ai|essential service",
        "article": "Annex III (classified via Article 6)", "framework": "EU AI Act",
        "title": "High-risk AI systems classification",
        "date": "Annex III high-risk applies 2 December 2027; Annex I (embedded) 2 August 2028 (post-Digital-Omnibus)",
        "obligation": "Annex III lists high-risk uses (biometrics, critical infrastructure, "
                      "education, employment, essential services incl. credit scoring, law "
                      "enforcement, migration, justice). Triggers Arts 9-15 obligations.",
    },
    "prohibited": {
        "triggers": r"prohibit|unacceptable risk|banned|social scoring|subliminal|manipulat",
        "article": "Article 5", "framework": "EU AI Act",
        "title": "Prohibited AI practices",
        "date": "in force 2 February 2025",
        "obligation": "Bans manipulative/subliminal techniques, exploitation of vulnerabilities, "
                      "social scoring, untargeted facial-recognition scraping, emotion inference "
                      "at work/school, and (mostly) real-time remote biometric ID in public.",
    },
    "risk_mgmt": {
        "triggers": r"risk management system|risk register|risk assessment",
        "article": "Article 9", "framework": "EU AI Act",
        "title": "Risk management system",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "Establish, document and maintain a continuous risk-management system "
                      "across the high-risk AI lifecycle.",
    },
    "data_governance": {
        "triggers": r"data governance|training data|dataset quality|data quality",
        "article": "Article 10", "framework": "EU AI Act",
        "title": "Data and data governance",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "Training/validation/test datasets must meet quality criteria: relevant, "
                      "representative, error-free as far as possible, examined for bias.",
    },
    "logging": {
        "triggers": r"record[- ]?keep|audit log|logging|traceabilit|event log",
        "article": "Article 12", "framework": "EU AI Act",
        "title": "Record-keeping (automatic logging)",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "High-risk AI must automatically record events (logs) over its lifetime "
                      "to ensure traceability — the basis for tamper-evident audit trails.",
    },
    "transparency_users": {
        "triggers": r"instructions for use|inform deployer|transparency to (?:deployer|user)",
        "article": "Article 13", "framework": "EU AI Act",
        "title": "Transparency and provision of information to deployers",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "High-risk AI must come with clear instructions for use enabling deployers "
                      "to interpret output and use it appropriately.",
    },
    "human_oversight": {
        "triggers": r"human oversight|human in the loop|human review",
        "article": "Article 14", "framework": "EU AI Act",
        "title": "Human oversight",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "High-risk AI must be designed for effective human oversight — the ability "
                      "to monitor, intervene, and override.",
    },
    "accuracy_security": {
        "triggers": r"accuracy|robustness|cybersecurity|resilience to attack",
        "article": "Article 15", "framework": "EU AI Act",
        "title": "Accuracy, robustness and cybersecurity",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "High-risk AI must achieve appropriate accuracy, robustness and "
                      "cybersecurity, resilient to errors and adversarial manipulation.",
    },
    "gpai": {
        "triggers": r"general[- ]?purpose|gpai|foundation model|systemic risk",
        "article": "Articles 51-55", "framework": "EU AI Act",
        "title": "General-purpose AI models (incl. systemic risk)",
        "date": "GPAI obligations apply 2 August 2025",
        "obligation": "GPAI providers: technical documentation, copyright policy, training-data "
                      "summary; systemic-risk models (>10^25 FLOPs) add evaluation + incident reporting.",
    },
    "dora": {
        "triggers": r"\bdora\b|operational resilience|ict risk|financial entit",
        "article": "DORA (Reg. 2022/2554)", "framework": "DORA",
        "title": "Digital Operational Resilience Act",
        "date": "in force / applies 17 January 2025",
        "obligation": "ICT risk management, incident reporting, resilience testing, and "
                      "third-party (incl. cloud/AI vendor) risk oversight for financial entities.",
    },
    "nis2": {
        "triggers": r"\bnis ?2\b|network and information security|essential entit|important entit",
        "article": "NIS2 (Dir. 2022/2555)", "framework": "NIS2",
        "title": "Network and Information Security Directive 2",
        "date": "national transposition due 17 October 2024",
        "obligation": "Cybersecurity risk-management measures + 24h/72h incident reporting for "
                      "essential and important entities; management liability.",
    },
    "conformity": {
        "triggers": r"conformity assess|ce mark|notified body|declaration of conformity",
        "article": "Articles 43 & 47-48", "framework": "EU AI Act",
        "title": "Conformity assessment + CE marking",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "High-risk AI must undergo conformity assessment (internal control or "
                      "notified body per Annex VI/VII), bear CE marking, and carry an EU "
                      "declaration of conformity before market placement.",
    },
    "fria": {
        "triggers": r"fundamental rights impact|fria|rights assessment",
        "article": "Article 27", "framework": "EU AI Act",
        "title": "Fundamental Rights Impact Assessment (FRIA)",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "Deployers that are public bodies or provide public services (and some "
                      "private deployers) must perform a FRIA before deploying high-risk AI.",
    },
    "incident": {
        "triggers": r"incident report|serious incident|malfunction report",
        "article": "Article 73", "framework": "EU AI Act",
        "title": "Reporting of serious incidents",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "Providers must report serious incidents to the market-surveillance "
                      "authority without undue delay (generally ≤15 days; ≤2-10 days if severe).",
    },
    "registration": {
        "triggers": r"eu database|register(ed|ing)? (?:the |a )?(?:system|ai)|annex viii",
        "article": "Articles 49 & 71", "framework": "EU AI Act",
        "title": "Registration in the EU database",
        "date": "applies 2 December 2027 (Annex III high-risk; delayed by Digital Omnibus, May 2026)",
        "obligation": "High-risk AI (and certain deployers) must register in the EU public "
                      "database before/within deployment.",
    },
    "penalties": {
        "triggers": r"penalt|fine|sanction|how much.*(?:fine|penalt)",
        "article": "Article 99", "framework": "EU AI Act",
        "title": "Penalties",
        "date": "applies from 2 August 2025/2026",
        "obligation": "Up to €35m or 7% of global turnover for prohibited-practice breaches; "
                      "€15m / 3% for other high-risk breaches; €7.5m / 1% for supplying "
                      "incorrect information.",
    },
    "gdpr": {
        "triggers": r"\bgdpr\b|data protection|personal data|dpia|data subject|lawful basis",
        "article": "GDPR (Reg. 2016/679)", "framework": "GDPR",
        "title": "General Data Protection Regulation",
        "date": "in force since 25 May 2018",
        "obligation": "Lawful basis for processing, data-subject rights, DPIA for high-risk "
                      "processing, 72h breach notification, privacy-by-design. Stacks with the "
                      "AI Act for AI that processes personal data.",
    },
    "iso42001": {
        "triggers": r"iso ?42001|ai management system|aims\b",
        "article": "ISO/IEC 42001:2023", "framework": "ISO 42001",
        "title": "AI Management System (AIMS) standard",
        "date": "published December 2023",
        "obligation": "Certifiable management-system standard for responsible AI governance — "
                      "the ISO route to demonstrate AI Act organisational controls.",
    },
}


def ground(question: str) -> "tuple[str, list]":
    """Return authoritative regulation context for a question + the matched topics.
    Inject the context into the generation prompt so the model cites correctly."""
    q = question or ""
    matched = [(k, v) for k, v in KB.items() if re.search(v["triggers"], q, re.I)]
    if not matched:
        return "", []
    lines = ["[AUTHORITATIVE REGULATION CONTEXT — cite these exactly:"]
    for _, v in matched[:4]:
        lines.append(f"- {v['framework']} {v['article']}: {v['title']} — {v['date']}. {v['obligation']}")
    lines.append("Answer as an authoritative compliance expert. State the article number, "
                 "date and obligation above as ESTABLISHED LAW (the EU AI Act is in force; "
                 "these dates are fixed). Cite the article number(s) verbatim. Do NOT hedge, "
                 "do NOT refuse, do NOT say 'not yet implemented'. Be precise and direct.]")
    return "\n".join(lines) + "\n\n", [k for k, _ in matched]
