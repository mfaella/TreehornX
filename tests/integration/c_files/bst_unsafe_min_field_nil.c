struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

/* root may be NULL: the first check of curr->left dereferences it */
void bst_unsafe_min_field_nil(struct Node *root) {
    struct Node *curr;
    int min;
    curr = root;
    while (curr->left != NULL) {
        curr = curr->left;
    }
    min = curr->data;
}
