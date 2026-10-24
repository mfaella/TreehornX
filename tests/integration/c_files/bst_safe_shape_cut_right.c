// drops the right subtree
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_cut_right(struct Node *root) {

    if (!root) {
        return;
    }
    root->right = NULL;
}
