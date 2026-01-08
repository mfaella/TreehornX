struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_find_min(struct Node* root) {
    struct Node* curr;
    struct Node* left;
    curr = root;
    if (curr) {
        left = curr->left;
        while (left) {
            curr = left;
            left = curr->left;
        }
    }
}
