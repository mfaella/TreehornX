// root->left is moved to root->right, then freed
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_free_moved(struct Node *root) {
    struct Node *c;
    if (!root) {
        return;
    }
    c = root->left;
    if (c) {
        root->left = NULL;
        root->right = c;
        free(c);
    }
}
