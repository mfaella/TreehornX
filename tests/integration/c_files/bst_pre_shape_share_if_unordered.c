// shares the right child under the left one when they are out of order
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_pre_shape_share_if_unordered(struct Node *root) {
    int a;
    int b;
    struct Node *l;
    struct Node *r;
    struct Node *lr;

    if (!root) {
        return;
    }
    l = root->left;
    r = root->right;
    if (!l) {
        return;
    }
    if (!r) {
        return;
    }
    lr = l->right;
    if (lr) {
        return;
    }
    a = l->data;
    b = r->data;
    if (a > b) {
        l->right = r;
    }
}
