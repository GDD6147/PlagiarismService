import re
import ast
import hashlib
import math
from difflib import SequenceMatcher
from typing import List, Tuple
from collections import Counter
from src.models import MethodResult

COMMON_KEYWORDS = {
    'if', 'else', 'for', 'while', 'return', 'class', 'def', 'using', 
    'namespace', 'public', 'private', 'protected', 'static', 'void',
    'int', 'string', 'bool', 'double', 'var', 'new', 'this', 'base'
}

class NormalizeMode:
    SIMPLE = "simple"
    TOKEN = "token"
    CHARACTER = "char"

class TokenizeMode:
    FULL = "full"
    IDENTIFIERS = "id"
    KEYWORDS = "kwords"

def detect_language(code: str) -> str:
    csharp_markers = ["using ", "namespace ", "public class", ";"]
    python_markers = ["def ", "import ", ":"]

    cs_score = sum(m in code for m in csharp_markers)
    py_score = sum(m in code for m in python_markers)

    return "csharp" if cs_score > py_score else "python"

def remove_comments(code: str, language: str) -> str:
    if language == "python":
        code = re.sub(r'#.*', '', code)
    else:
        code = re.sub(r'//.*', '', code)
        code = re.sub(r'/\*[\s\S]*?\*/', '', code)
        code = re.sub(r'#.*', '', code)
    return code

def normalize_code(code: str, language: str, mode: str = NormalizeMode.SIMPLE):
    code = remove_comments(code, language)
    
    match mode:
        case NormalizeMode.SIMPLE:
            lines = [line.strip() for line in code.splitlines() if line.strip()]
            return "\n".join(lines)
        case NormalizeMode.CHARACTER:
            code = re.sub(r'\s+', '', code)
            code = re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', 'ID', code)
            return code
        case NormalizeMode.TOKEN:
            tokens = tokenize_code(code, mode = TokenizeMode.FULL)
            normalized = []
            for token in tokens:
                if token.isalpha() and token not in COMMON_KEYWORDS:
                    normalized.append('VAR')
                else:
                    normalized.append(token)
            return normalized

def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    if b == 0 or math.isnan(a) or math.isnan(b):
        return default
    result = a / b
    return default if math.isnan(result) else result

def tokenize_code(code: str, mode: str = TokenizeMode.FULL) -> List[str]:
    patterns = {
        'identifiers': r'[a-zA-Z_]\w*',
        'numbers': r'\b\d+\b',
        'operators': r'[+\-*/=<>!&|]+',
        'punctuation': r'[{}()\[\];,.]',
        'strings': r'"[^"]*"|\'[^\']*\'',
        'keywords': r'\b(' + '|'.join(COMMON_KEYWORDS) + r')\b|[+\-*/=<>!&|;{}()]'
    }
    
    tokens = []

    match mode:
        case TokenizeMode.FULL:
            for pattern in patterns.values():
                tokens.extend(re.findall(pattern, code))
        case TokenizeMode.IDENTIFIERS:
            tokens = re.findall(patterns['identifiers'], code)
        case TokenizeMode.KEYWORDS:
            matches = re.findall(patterns['keywords'], code)
            tokens = [t for match in matches for t in (match if isinstance(match, tuple) else (match,)) if t]
        case _:
            raise ValueError(f"Unknown normalization mode: {mode}")
    
    return tokens

# МЕТОДЫ СРАВНЕНИЯ

# 1. AST-анализ
def get_ast_sequence(code: str, language: str) -> List[str]:

    if language == "python":
        try:
            tree = ast.parse(code)
            return [type(node).__name__ for node in ast.walk(tree)]
        except SyntaxError:
            return []
    else:
        patterns = {
            "class": r"\bclass\b",
            "method": r"\b(public|private|protected)\s+\w+\s+\w+\s*\(",
            "property": r"\b(public|private|protected)\s+\w+\s+\w+\s*\{\s*get;\s*set;\s*\}",
            "if": r"\bif\s*\(",
            "for": r"\bfor\s*\(",
            "foreach": r"\bforeach\s*\(",
            "while": r"\bwhile\s*\(",
            "return": r"\breturn\b",
            "try": r"\btry\b",
            "catch": r"\bcatch\s*\(",
        }
        
        nodes = []
        for name, pattern in patterns.items():
            nodes.extend([name] * len(re.findall(pattern, code, re.MULTILINE)))
        return nodes

def ast_similarity(code_a: str, code_b: str, language: str) -> float:
    ast_a = get_ast_sequence(code_a, language)
    ast_b = get_ast_sequence(code_b, language)
    result = SequenceMatcher(None, ast_a, ast_b).ratio()
    return 0.0 if math.isnan(result) else result

# 2. Стандартный шинглинг
def shingling_similarity(code_a: str, code_b: str, k: int = 5, language: str = "python") -> float:
    norm_a = normalize_code(code_a, language, NormalizeMode.TOKEN)
    norm_b = normalize_code(code_b, language, NormalizeMode.TOKEN)
    
    if len(norm_a) < k or len(norm_b) < k:
        return 0.0
    
    def get_ngrams(tokens, n):
        return {" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)}
    
    ngrams_a = get_ngrams(norm_a, k)
    ngrams_b = get_ngrams(norm_b, k)
    
    if not ngrams_a or not ngrams_b:
        return 0.0
    
    intersection = len(ngrams_a & ngrams_b)
    union = len(ngrams_a | ngrams_b)
    return safe_divide(intersection, union)


# 2.1 Символьный шинглинг
def character_shingling_similarity(code_a: str, code_b: str, k: int = 10, language: str = "python") -> float:
    norm_a = normalize_code(code_a, language, NormalizeMode.CHARACTER)
    norm_b = normalize_code(code_b, language, NormalizeMode.CHARACTER)
    
    if len(norm_a) < k or len(norm_b) < k:
        return 0.0
    
    def get_ngrams(text, n):
        return {text[i:i+n] for i in range(len(text) - n + 1)}
    
    ngrams_a = get_ngrams(norm_a, k)
    ngrams_b = get_ngrams(norm_b, k)
    
    if not ngrams_a or not ngrams_b:
        return 0.0
    
    intersection = len(ngrams_a & ngrams_b)
    union = len(ngrams_a | ngrams_b)
    return safe_divide(intersection, union)


# 2.2 Структурный шинглинг
def structural_shingling_similarity(code_a: str, code_b: str, k: int = 3, language: str = "python") -> float:
    tokens_a = tokenize_code(code_a, TokenizeMode.KEYWORDS)
    tokens_b = tokenize_code(code_b, TokenizeMode.KEYWORDS)
    
    if len(tokens_a) < k or len(tokens_b) < k:
        return 0.0
    
    def get_ngrams(tokens, n):
        return {" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)}
    
    ngrams_a = get_ngrams(tokens_a, k)
    ngrams_b = get_ngrams(tokens_b, k)
    
    if not ngrams_a or not ngrams_b:
        return 0.0
    
    intersection = len(ngrams_a & ngrams_b)
    union = len(ngrams_a | ngrams_b)
    return safe_divide(intersection, union)

# 3. Хеширование блоков
def extract_code_blocks(code: str, block_size: int = 3) -> List[str]:
    lines = [line.strip() for line in code.split('\n') if line.strip()]
    blocks = []
    
    for i in range(0, len(lines), block_size):
        block = ' '.join(lines[i:i+block_size])
        if block:
            blocks.append(block)
    return blocks


def hash_similarity(code_a: str, code_b: str, block_size: int = 3) -> float:
    blocks_a = extract_code_blocks(code_a, block_size)
    blocks_b = extract_code_blocks(code_b, block_size)
    
    if not blocks_a or not blocks_b:
        return 0.0
    
    def get_block_hash(block: str) -> str:
        normalized = re.sub(r'\s+', ' ', block.strip().lower())
        return hashlib.md5(normalized.encode()).hexdigest()
    
    hashes_a = {get_block_hash(block) for block in blocks_a}
    hashes_b = {get_block_hash(block) for block in blocks_b}
    
    intersection = len(hashes_a & hashes_b)
    union = len(hashes_a | hashes_b)
    return safe_divide(intersection, union)


# 4. Косинусное сходство
def cosine_similarity_code(code_a: str, code_b: str) -> float:
    tokens_a = tokenize_code(code_a, mode = TokenizeMode.FULL)
    tokens_b = tokenize_code(code_b, mode = TokenizeMode.FULL)
    
    if not tokens_a or not tokens_b:
        return 0.0
    
    vec_a = Counter(tokens_a)
    vec_b = Counter(tokens_b)
    
    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    dot_product = sum(vec_a[key] * vec_b[key] for key in common_keys)
    
    norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return safe_divide(dot_product, norm_a * norm_b)


# # 5. Расстояние Левенштейна
# def levenshtein_distance(s1: str, s2: str) -> int:
#     if len(s1) < len(s2):
#         return levenshtein_distance(s2, s1)
    
#     if len(s2) == 0:
#         return len(s1)
    
#     previous_row = list(range(len(s2) + 1))
#     for i, c1 in enumerate(s1):
#         current_row = [i + 1]
#         for j, c2 in enumerate(s2):
#             insertions = previous_row[j + 1] + 1
#             deletions = current_row[j] + 1
#             substitutions = previous_row[j] + (c1 != c2)
#             current_row.append(min(insertions, deletions, substitutions))
#         previous_row = current_row
    
#     return previous_row[-1]


# def levenshtein_similarity(code_a: str, code_b: str) -> float:
#     normalized_a = re.sub(r'\s+', ' ', code_a.strip())
#     normalized_b = re.sub(r'\s+', ' ', code_b.strip())
    
#     if not normalized_a and not normalized_b:
#         return 1.0
#     if not normalized_a or not normalized_b:
#         return 0.0
    
#     distance = levenshtein_distance(normalized_a, normalized_b)
#     max_len = max(len(normalized_a), len(normalized_b))
#     similarity = 1 - (distance / max_len) if max_len > 0 else 0.0
#     return max(0.0, 0.0 if math.isnan(similarity) else similarity)


# # 6. Jaccard (дополнительный метод)
# def jaccard_similarity(code_a: str, code_b: str) -> float:
#     tokens_a = set(tokenize_code(code_a, mode = TokenizeMode.IDENTIFIERS))
#     tokens_b = set(tokenize_code(code_b, mode = TokenizeMode.IDENTIFIERS))
    
#     if not tokens_a or not tokens_b:
#         return 0.0
    
#     intersection = len(tokens_a & tokens_b)
#     union = len(tokens_a | tokens_b)
#     return safe_divide(intersection, union)


# Основная функция
def compare_codes_with_methods(code_a: str, code_b: str, language: str) -> Tuple[float, List[MethodResult]]:
    norm_a = normalize_code(code_a, language, NormalizeMode.SIMPLE)
    norm_b = normalize_code(code_b, language, NormalizeMode.SIMPLE)

    ast_sim = ast_similarity(norm_a, norm_b, language)
    shingling_standard_sim = shingling_similarity(norm_a, norm_b)
    shingling_char_sim = character_shingling_similarity(norm_a, norm_b)
    shingling_struct_sim = structural_shingling_similarity(norm_a, norm_b)
    print()
    combined_shingling = max(shingling_standard_sim, shingling_char_sim, shingling_struct_sim)
    hash_sim = hash_similarity(norm_a, norm_b)
    cosine_sim = cosine_similarity_code(norm_a, norm_b)

    weights = {
        'ast': 0.30,
        'shingling': 0.25,
        'hashing': 0.20,
        'cosine': 0.25,
    }
    
    combined_similarity = (
        weights['ast'] * (0.0 if math.isnan(ast_sim) else ast_sim) +
        weights['shingling'] * (0.0 if math.isnan(combined_shingling) else combined_shingling) +
        weights['hashing'] * (0.0 if math.isnan(hash_sim) else hash_sim) +
        weights['cosine'] * (0.0 if math.isnan(cosine_sim) else cosine_sim)
    )
    
    methods_results = [
        MethodResult(
            methodName="AST Structural Analysis",
            similarity=round(ast_sim, 4),
            details={"ast_nodes_a": len(get_ast_sequence(norm_a, language)), 
                    "ast_nodes_b": len(get_ast_sequence(norm_b, language))}
        ),
        MethodResult(
            methodName="Shingling (n-grams)",
            similarity=round(combined_shingling, 4),
            details={"methods": "Token + Character + Structural n-grams"}
        ),
        MethodResult(
            methodName="Hashing (MD5 blocks)",
            similarity=round(hash_sim, 4),
            details={"blocks_a": len(extract_code_blocks(norm_a)), 
                    "blocks_b": len(extract_code_blocks(norm_b))}
        ),
        MethodResult(
            methodName="Cosine Similarity",
            similarity=round(cosine_sim, 4),
            details={"unique_tokens_a": len(set(tokenize_code(norm_a, mode = TokenizeMode.FULL))), 
                    "unique_tokens_b": len(set(tokenize_code(norm_b, mode = TokenizeMode.FULL)))}
        ),
        MethodResult(
            methodName="Combined Method",
            similarity=round(combined_similarity, 4),
            details=weights
        )
    ]
    
    return combined_similarity, methods_results