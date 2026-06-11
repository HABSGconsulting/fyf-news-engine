# Lookup tables: script uses these to auto-fill frontmatter fields
# AI never needs to know these mappings

CATEGORY_TO_ORG_RELEVANCE = {
    "macro":       ["mf_house", "bank", "mfd_network", "insurance"],
    "regulatory":  ["mf_house", "mfd_network", "ria_firm"],
    "taxation":    ["mf_house", "mfd_network", "ria_firm", "corporate"],
    "product":     ["mf_house", "mfd_network"],
    "performance": ["mf_house", "stockbroker"],
    "sectoral":    ["stockbroker", "mf_house"],
    "behavioral":  ["mf_house", "mfd_network", "media"],
    "house":       ["mf_house", "mfd_network"],
}

CATEGORY_TO_BOOK_CHAPTERS = {
    "macro":       ["debt_markets", "monetary_policy", "asset_allocation"],
    "regulatory":  ["regulatory_framework", "compliance"],
    "taxation":    ["tax_planning", "financial_planning"],
    "product":     ["mutual_fund_basics", "etf_indexing"],
    "performance": ["fund_analysis", "benchmarking"],
    "sectoral":    ["equity_markets", "concentration_risk"],
    "behavioral":  ["behavioral_finance", "investor_psychology"],
    "house":       ["fund_house_analysis", "process_risk"],
}

CATEGORY_TO_RELATED_BOOKS = {
    "macro":       ["Personal Finance Fundamentals", "PASS Research Analyst Certification"],
    "regulatory":  ["PASS Research Analyst Certification"],
    "taxation":    ["Personal Finance Fundamentals"],
    "product":     ["Personal Finance Fundamentals", "PASS Research Analyst Certification"],
    "performance": ["PASS Research Analyst Certification"],
    "sectoral":    ["PASS Research Analyst Certification"],
    "behavioral":  ["Personal Finance Fundamentals"],
    "house":       ["PASS Research Analyst Certification"],
}

EVENT_SERIES_CYCLES = {
    "RBI_MPC":             "bi_monthly",
    "UNION_BUDGET":        "annual",
    "SEBI_BOARD":          "quarterly",
    "QUARTERLY_RESULTS":   "quarterly",
    "ANNUAL_INFLATION":    "annual",
    "NIFTY_MILESTONE":     "irregular",
    "FII_FLOW_TREND":      "irregular",
}

PRONUNCIATION_MAP = {
    "SEBI":   "Sebee",
    "ELSS":   "E L S S",
    "NFO":    "N F O",
    "NAV":    "N A V",
    "FII":    "F I I",
    "DII":    "D I I",
    "AUM":    "A U M",
    "TER":    "T E R",
    "LTCG":   "L T C G",
    "STCG":   "S T C G",
    "AMFI":   "Amfi",
    "NBFC":   "N B F C",
    "NPS":    "N P S",
    "PPF":    "P P F",
    "EPFO":   "E P F O",
    "NSE":    "N S E",
    "BSE":    "B S E",
}
