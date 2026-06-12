import sys
import z3
import graphviz

def solve_and_render_chc(smt2_file=None):
    # 1. CRITICAL: Proof generation must be enabled before creating any solver or parsing
    z3.set_param(proof=True)

    # 2. Initialize the Horn solver (Spacer engine)
    solver = z3.SolverFor("HORN")

    if smt2_file:
        print(f"Parsing CHC system from {smt2_file}...")
        try:
            assertions = z3.parse_smt2_file(smt2_file)
            solver.add(assertions)
        except Exception as e:
            print(f"Failed to parse file: {e}")
            sys.exit(1)
    else:
        print("No file provided. Generating a dummy UNSAT CHC system for demonstration...")
        I = z3.IntSort()
        P = z3.Function('P', I, z3.BoolSort())
        x = z3.Int('x')

        # Fact: P(5) is True
        solver.add(P(5))
        # Rule: P(x) => False (Target)
        solver.add(z3.ForAll([x], z3.Implies(P(x), z3.BoolVal(False))))

    # 3. Check Satisfiability
    print("Checking CHC system...")
    res = solver.check()

    if res == z3.sat:
        print("Result: SAT. The system is safe (no witness/counterexample to extract).")
    elif res == z3.unsat:
        print("Result: UNSAT. Property violated. Extracting witness...")
        proof = solver.proof()
        render_proof(proof)
    else:
        print(f"Unknown solver result: {res}")

def render_proof(proof_node, output_filename="chc_witness"):
    """
    Traverses the Z3 proof AST safely and applies layout constraints
    to prevent librsvg 'InvalidSize' rendering errors on massive CHC trees.
    """
    # Create a directed graph with strict size-limiting constraints
    dot = graphviz.Digraph(
        comment="CHC Witness Proof",
        node_attr={
            'shape': 'box',
            'fontname': 'Courier',
            'style': 'filled',
            'fillcolor': '#f9f9f9',
            'fontsize': '10',         # Smaller font size
            'height': '0.1',          # Allows nodes to shrink to content
            'width': '0.1'
        }
    )

    # Graph-level attributes to scale down the layout
    dot.attr(rankdir='LR')            # Left-to-Right layout fits wide trees much better
    dot.attr(nodesep='0.2')           # Tighter packing between nodes
    dot.attr(ranksep='0.3')           # Tighter packing between tree layers

    visited = set()

    def format_node_text(text):
        """Splits long SMT-LIB expressions across multiple lines instead of one huge row."""
        text = text.replace('\n', ' ')
        max_line_len = 50

        # Hard truncate if the proof step is astronomically massive
        if len(text) > 300:
            text = text[:140] + " ... [TRUNCATED] ... " + text[-140:]

        # Wrap lines smoothly every ~50 characters
        words = text.split(' ')
        lines = []
        current_line = []
        current_len = 0
        for word in words:
            if current_len + len(word) > max_line_len:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_len = len(word)
            else:
                current_line.append(word)
                current_len += len(word) + 1
        if current_line:
            lines.append(" ".join(current_line))

        return "\n".join(lines)

    def traverse(node):
        node_id = str(node.get_id())

        if node_id in visited:
            return node_id

        visited.add(node_id)

        # Safe Type Checking
        if z3.is_app(node):
            rule_name = node.decl().name()
        elif z3.is_quantifier(node):
            rule_name = "Quantifier"
        elif z3.is_var(node):
            rule_name = "Variable"
        else:
            rule_name = "Term"

        # Format and wrap text to constrain structural width
        formatted_text = format_node_text(str(node))
        label_plain = f"[{rule_name}]\n{formatted_text}"

        # Highlight target state violation
        if "false" in str(node).lower() and rule_name != "asserted":
            dot.node(node_id, label=label_plain, fillcolor="#ffcccc")
        else:
            dot.node(node_id, label=label_plain)

        # Recurse through premises
        for child in node.children():
            child_id = traverse(child)
            dot.edge(child_id, node_id)

        return node_id

    print("Traversing complex proof tree and applying layout compression...")
    traverse(proof_node)

    try:
        # Render the file
        dot.render(output_filename, format="pdf", view=True)
        print(f"Witness successfully compressed and rendered to {output_filename}.pdf")
    except graphviz.backend.execute.ExecutableNotFound:
        print("\n[ERROR] Graphviz executable not found!")
    except Exception as e:
        print(f"Error rendering graph: {e}")

if __name__ == "__main__":
    # If an SMT2 file is passed via CLI, use it; otherwise run the dummy example.
    target_file = sys.argv[1] if len(sys.argv) > 1 else None
    solve_and_render_chc(target_file)
