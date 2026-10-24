// swaps the first two nodes forgetting to relink the first
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_swap_no_fix(struct Node *root) {
    struct Node *a;
    struct Node *b;

    a = root;
    if (!a) {
        return;
    }
    b = a->next;
    if (!b) {
        return;
    }
    b->next = a;
    root = b;
}
