// complete reverse, then the old head points to the new one
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_reverse_back_edge(struct Node *root) {
    struct Node *y;
    struct Node *tmp;
    struct Node *first;

    y = NULL;
    first = root;
    while (first) {
        tmp = first->next;
        first->next = y;
        y = first;
        first = tmp;
    }
    if (root) {
        root->next = y;
    }
    root = y;
}
