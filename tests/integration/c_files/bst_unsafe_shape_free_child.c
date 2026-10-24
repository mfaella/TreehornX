// root->left is freed but still linked
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_free_child(struct Node *root) {
    struct Node *c;
    if (!root) {
        return;
    }
    c = root->left;
    if (c) {
        free(c);
    }
}
