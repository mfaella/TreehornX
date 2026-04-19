struct Node {
    int value;
    struct Node *next;
};

void sll_safe_reverse(struct Node *root) {
    struct Node *y;
    struct Node *tmp;
    struct Node *first;

    first = root;

    while(first) {
        tmp = first->next;
        first->next = y;
        y = first;
        first = tmp;
    }

    root = y;
}
