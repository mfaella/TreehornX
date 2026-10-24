// the left grandchild is also the right child of the left child
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_share_grandchild(struct Node *root) {
    struct Node *l;
    struct Node *ll;

    if (!root) {
        return;
    }
    l = root->left;
    if (!l) {
        return;
    }
    ll = l->left;
    l->right = ll;
}
