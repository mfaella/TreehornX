struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_find_min(struct Node* root) {
    struct Node* curr;
    struct Node* left;
    curr = root;
    if (curr != 0) {
        left = curr->left;
        while (left != 0) {
            curr = left;
            left = curr->left;
        }
    }
}
