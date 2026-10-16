struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_min_field_nil(struct Node *root) {
    struct Node *curr;
    int min;
    if (root != NULL) {
        curr = root;
        while (curr->left != NULL) {
            curr = curr->left;
        }
        min = curr->data;
    }
}
