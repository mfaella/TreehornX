// cycle when the right child is smaller than the root: impossible in a bst
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_pre_shape_right_smaller(struct Node *root) {
    int a;
    int b;
    struct Node *r;

    if (!root) {
        return;
    }
    r = root->right;
    if (!r) {
        return;
    }
    a = r->data;
    b = root->data;
    if (a < b) {
        r->right = root;
    }
}
