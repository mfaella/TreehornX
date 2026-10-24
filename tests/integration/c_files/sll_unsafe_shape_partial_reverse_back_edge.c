// partial reverse reattaching the new head instead of the rest
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_partial_reverse_back_edge(struct Node *root) {
    int key;
    int d;
    struct Node *y;
    struct Node *tmp;
    struct Node *first;

    y = NULL;
    first = root;
    while (first) {
        d = first->data;
        if (d > key) {
            break;
        }
        tmp = first->next;
        first->next = y;
        y = first;
        first = tmp;
    }
    if (y) {
        root->next = y;
        root = y;
    }
}
