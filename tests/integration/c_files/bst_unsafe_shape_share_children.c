// root->left == root->right

// leftmost->left = root
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_share_children(struct Node *root) {
    struct Node *tmp;

    if (!root) {
        return;
    }

    tmp = root->right;
    root->left = tmp;
}
