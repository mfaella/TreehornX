// root->left and root->right both point to the new node
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_two_fields(struct Node *root) {
    struct Node *tmp;
    if (!root) {
        return;
    }
    tmp = malloc(sizeof(struct Node));
    root->left = tmp;
    root->right = tmp;
}
