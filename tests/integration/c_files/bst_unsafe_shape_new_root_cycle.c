// a new root that is also the right child of the old one
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_new_root_cycle(struct Node *root) {
    struct Node *n;

    if (!root) {
        return;
    }
    n = malloc(sizeof(struct Node));
    n->left = root;
    root->right = n;
    root = n;
}
