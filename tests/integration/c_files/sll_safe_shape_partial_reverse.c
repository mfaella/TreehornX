// reverses the prefix of nodes with data <= key, then reattaches the rest
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_partial_reverse(struct Node *root) {
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
        root->next = first;
        root = y;
    }
}
