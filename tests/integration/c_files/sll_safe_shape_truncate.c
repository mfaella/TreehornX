// keeps only the head, freeing the rest
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_truncate(struct Node *root) {
    struct Node *rest;
    struct Node *nxt;

    if (!root) {
        return;
    }
    rest = root->next;
    root->next = NULL;
    while (rest) {
        nxt = rest->next;
        free(rest);
        rest = nxt;
    }
}
