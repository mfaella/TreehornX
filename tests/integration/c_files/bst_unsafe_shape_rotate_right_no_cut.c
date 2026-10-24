// right rotation forgetting root->left := l->right
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_rotate_right_no_cut(struct Node *root) {
    struct Node *l;

    if (!root) {
        return;
    }
    l = root->left;
    if (!l) {
        return;
    }
    l->right = root;
    root = l;
}
