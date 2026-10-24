// complete reverse
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_reverse(struct Node *root) {
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
    root = y;
}
