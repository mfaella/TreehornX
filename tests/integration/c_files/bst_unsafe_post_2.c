// leftmost->left = root
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_post_2(struct Node *root) {
    struct Node *current;
    struct Node *leftMost;
    struct Node *rightMost;

    if (!root) {
        return;
    }

    leftMost = root;
    current = root->left;
    while(current) {
        leftMost = current;
        current = current->left;
    }

    leftMost->left = root;
}
