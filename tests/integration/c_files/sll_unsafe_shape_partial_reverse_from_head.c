// partial reverse starting with y = root
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_partial_reverse_from_head(struct Node *root) {
    int key;
    int d;
    struct Node *y;
    struct Node *tmp;
    struct Node *first;

    if (!root) {
        return;
    }
    y = root;
    first = root->next;
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
    root = y;
}
