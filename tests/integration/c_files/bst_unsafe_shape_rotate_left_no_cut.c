// left rotation forgetting root->right := r->left
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_rotate_left_no_cut(struct Node *root) {
    struct Node *r;

    if (!root) {
        return;
    }
    r = root->right;
    if (!r) {
        return;
    }
    r->left = root;
    root = r;
}
