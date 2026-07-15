#!/usr/bin/env python3
"""
injection-detector.sh — UserPromptSubmit hook
Fast regex-only detection of four injection categories.
Exits 2 on match; exit 0 on no match (never blocks the session on error).
"""

import sys
import json
import re
import os

# Resolve project directory (for consistency, though this hook is stateless)
project_dir = os.getenv('DE_AGENT_PROJECT_DIR') or os.getenv('CLAUDE_PROJECT_DIR') or '.'

try:
    json_input = json.load(sys.stdin)
    prompt = json_input.get('prompt', '')
except (json.JSONDecodeError, ValueError, EOFError):
    # Malformed input — pass through (don't break the session)
    sys.exit(0)

if not prompt:
    sys.exit(0)

# Normalize CRs to spaces (as per spec)
prompt_normalized = prompt.replace('\r', ' ')

# Compile patterns with case-insensitive flag and using re.IGNORECASE
# Patterns are designed to not match themselves in the source code (e.g., by using char classes or splits)

patterns = [
    # Category 1: Instruction override
    # English: "ignore (all/any/the/your)? (previous/prior/system/developer)? (instructions/prompts/rules/guardrails)"
    # CJK: "忽略/无视/忘记/抛开 ... 系统提示/提示词/指令" or verbs + "你的" + "规则/限制/约束/命令/权限"
    (r"ignore\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|system|developer)?\s*(instructions?|prompts?|rules?|guardrails?)", "Instruction override"),
    (r"(?:忽略|无视|忘记|抛开)\s*(?:系统提示|提示词|指令)", "Instruction override (CJK)"),
    (r"(?:忽略|无视|忘记|抛开)\s*你的\s*(?:规则|限制|约束|命令|权限)", "Instruction override (CJK with possessive)"),

    # Category 2: Hidden-prompt exfiltration
    # English: "(reveal/show/print/dump/display/expose) (system prompt/developer prompt/hidden prompt/secret rules/guardrails)"
    # CJK: "显示/展示/输出/打印/告诉我/发给我/泄露/列出 ... 系统提示/提示词/隐藏的提示或规则/初始指令/你的指令"
    (r"(?:reveal|show|print|dump|display|expose)\s+(?:(?:system|developer|hidden|secret)\s+)?(?:prompts?|rules?|guardrails?)", "Hidden-prompt exfiltration"),
    (r"(?:显示|展示|输出|打印|告诉我|发给我|泄露|列出)\s*(?:系统提示|提示词|隐藏的提示|隐藏的规则|初始指令)", "Hidden-prompt exfiltration (CJK)"),
    (r"(?:显示|展示|输出|打印|告诉我|发给我|泄露|列出)\s*你的\s*指令", "Hidden-prompt exfiltration - your instructions (CJK)"),

    # Category 3: Guardrail bypass
    # English: "(bypass/disable/turn off/remove/skip) (security/safeguards/guardrails/policy/policies/restrictions/hooks/permissions)"
    # CJK: "绕过/绕开/关闭/禁用/停用/解除/跳过/移除/无视 ... 护栏/安全护栏/注入检测/审查机制/防护机制"
    (r"(?:bypass|disable|turn\s+off|remove|skip)\s+(?:security|safeguards?|guardrails?|policies?|restrictions?|hooks?|permissions?)", "Guardrail bypass"),
    (r"(?:绕过|绕开|关闭|禁用|停用|解除|跳过|移除|无视)\s*(?:护栏|安全护栏|注入检测|审查机制|防护机制)", "Guardrail bypass (CJK)"),
    (r"(?:绕过|绕开|关闭|禁用|停用|解除|跳过|移除|无视)\s*你的\s*(?:限制|约束|防护|安全|规则|审查|检查|权限)", "Guardrail bypass - your restrictions (CJK)"),

    # Category 4: Destructive payload smuggling
    # Patterns for rm -rf /, mkfs*, dd if=... of=/dev/*, curl|sh, wget|sh
    (r"(?:run|execute|bash|shell|launch).*(?:rm\s+-rf\s+(?:/|~|--no-preserve-root)|mkfs|dd\s+if=|curl.*\|.*sh|wget.*\|.*sh)", "Destructive payload smuggling"),
    (r"(?:执行|运行|帮我跑|帮我执行|跑一下).*(?:rm\s+-rf|mkfs|dd\s+if=|curl.*\|.*sh|wget.*\|.*sh)", "Destructive payload smuggling (CJK)"),
]

for pattern_str, category in patterns:
    try:
        if re.search(pattern_str, prompt_normalized, re.IGNORECASE | re.DOTALL):
            # Match found — exit 2 with reason on stderr
            sys.stderr.write(f"Injection detected: {category}\n")
            sys.exit(2)
    except re.error:
        # Regex compilation error — don't break, just skip this pattern
        pass

# No matches — allow
sys.exit(0)
