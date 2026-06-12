struct Node {
    int data;
    struct Node *next;
};

void sll_safe_append_left(struct Node *root, int value) {
    struct Node *first;

    first = malloc(sizeof(struct Node));
    first->data = value;

    if (root) {
        first->next = root;
    }

    root = first;
}
