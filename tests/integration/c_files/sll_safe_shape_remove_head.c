// removes and frees the head
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_remove_head(struct Node *root) {
    struct Node *tmp;

    if (!root) {
        return;
    }
    tmp = root->next;
    free(root);
    root = tmp;
}
