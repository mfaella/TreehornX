// reverses two nodes with a counter, reattaching the new head
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_partial_reverse_two_back_edge(struct Node *root) {
    int i;
    struct Node *y;
    struct Node *tmp;
    struct Node *first;

    i = 0;
    y = NULL;
    first = root;
    while (first) {
        if (i >= 2) {
            break;
        }
        tmp = first->next;
        first->next = y;
        y = first;
        first = tmp;
        i = i + 1;
    }
    if (y) {
        root->next = y;
        root = y;
    }
}
