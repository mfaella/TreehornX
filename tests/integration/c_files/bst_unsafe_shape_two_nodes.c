// root->right and root->left->left both point to the new node
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_two_nodes(struct Node *root) {
    struct Node *c;
    struct Node *tmp;
    if (!root) {
        return;
    }
    c = root->left;
    if (!c) {
        return;
    }
    tmp = malloc(sizeof(struct Node));
    root->right = tmp;
    c->left = tmp;
}
