// the root is its own right child
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_self_loop(struct Node *root) {

    if (!root) {
        return;
    }
    root->right = root;
}
