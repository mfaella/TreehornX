// the output starts at the second node
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_drop_head(struct Node *root) {
    struct Node *tmp;

    if (!root) {
        return;
    }
    tmp = root->next;
    root = tmp;
}
