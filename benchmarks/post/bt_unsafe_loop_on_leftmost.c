struct Node {
    struct Node *left;
    struct Node *right;
    int data;
};

void bt_unsafe_loop_on_leftmost(struct Node *root) {
    struct Node *current;
    struct Node *tmp;

    if(!root) {
        return;
    }

    tmp = root;
    current = root->left;

    while(current) {
        tmp = current;
        current = current->left;
    }

    tmp->left = tmp;
}
