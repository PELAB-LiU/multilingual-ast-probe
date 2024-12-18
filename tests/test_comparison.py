import unittest

import matplotlib.pyplot as plt
import networkx as nx

from src.data.binary_tree import ast2binary, tree_to_distance
from src.data.code2ast import code2ast, get_tokens_ast
from src.data.data_loading import PARSER_OBJECT_BY_NAME

code_python = """def max(a,b):
    if a > b:
        return a
    return b"""

code_java = """public static int max(int a, int b) {
    if (a > b) {
        return a;
    }
    return b;
}"""

code_csharp = """public static int max(int a, int b) {
    if (a > b) {
        return a;
    }
    return b;
}"""


def print_beautiful(tokens, c, d):
    result = ""
    for j, c_j in enumerate(c):
        result += f"[{tokens[j]}]" + f"-{c_j}{d[j]}-"
    result += tokens[-1]
    return result


class Comparison(unittest.TestCase):
    def test_java(self):
        parser = PARSER_OBJECT_BY_NAME['java']
        G, pre_code = code2ast(code_java, parser, lang='java')
        binary_ast = ast2binary(G)
        d, c, _, u = tree_to_distance(binary_ast, 0)
        print(print_beautiful(get_tokens_ast(G, pre_code), c, d))
        nx.draw(nx.Graph(G), labels=nx.get_node_attributes(G, 'type'), with_labels=True)
        plt.show()
        print(d)
        print(get_tokens_ast(G, pre_code))

    def test_csharp(self):
        parser = PARSER_OBJECT_BY_NAME['csharp']
        G, pre_code = code2ast(code_csharp, parser, lang='csharp')
        binary_ast = ast2binary(G)
        d, c, _, u = tree_to_distance(binary_ast, 0)
        print(print_beautiful(get_tokens_ast(G, pre_code), c, d))
        nx.draw(nx.Graph(G), labels=nx.get_node_attributes(G, 'type'), with_labels=True)
        plt.show()
        print(d)
        print(get_tokens_ast(G, pre_code))


if __name__ == '__main__':
    unittest.main()
