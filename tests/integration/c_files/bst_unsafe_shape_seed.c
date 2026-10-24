// root->right and root->left->left both point to the new node; the lace goes down from the update of root->right
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};
void bst_unsafe_shape_seed(struct Node *root) {
    struct Node *c;
    struct Node *tmp;
    if (!root) {
        return;
    }
    tmp = malloc(sizeof(struct Node));
    root->right = tmp;
    c = root->left;
    if (!c) {
        return;
    }
    c->left = tmp;
}
