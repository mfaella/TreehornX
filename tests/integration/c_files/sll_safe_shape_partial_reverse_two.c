// reverses the first two nodes with a counter, then reattaches the rest
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_partial_reverse_two(struct Node *root) {
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
        root->next = first;
        root = y;
    }
}
