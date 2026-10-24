// swaps the children of the left child
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_mirror_left(struct Node *root) {
    struct Node *l;
    struct Node *a;
    struct Node *b;

    if (!root) {
        return;
    }
    l = root->left;
    if (!l) {
        return;
    }
    a = l->left;
    b = l->right;
    l->left = b;
    l->right = a;
}
