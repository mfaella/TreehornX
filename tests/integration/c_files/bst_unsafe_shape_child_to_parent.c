// the left child points back to the root
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_child_to_parent(struct Node *root) {
    struct Node *l;

    if (!root) {
        return;
    }
    l = root->left;
    if (!l) {
        return;
    }
    l->left = root;
}
