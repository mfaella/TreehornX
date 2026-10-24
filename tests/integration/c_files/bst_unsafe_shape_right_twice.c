// both fields of the root point to the right child
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_right_twice(struct Node *root) {
    struct Node *r;

    if (!root) {
        return;
    }
    r = root->right;
    root->left = r;
    root->right = r;
}
