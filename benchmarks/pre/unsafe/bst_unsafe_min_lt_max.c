struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_min_lt_max(struct Node *root) {
    struct Node *tmp;
    struct Node *current;
    int min;
    int max;
    _Bool singleton;
    singleton = true;
    if(!root) {
        return;
    }
    tmp = root->left;
    if(!tmp) {
        min = root->data;
    }
    else {
        singleton = false;
        current = root;
        while(current) {
            tmp = current;
            current = current->left;
        }
        min = tmp->data;
    }
    tmp = root->right;
    if(!tmp) {
        max = root->data;
    }
    else {
        singleton = false;
        current = root;
        while(current) {
            tmp = current;
            current = current->right;
        }
        max = tmp->data;
    }
    if (!singleton && min < max) {
        min = current->data;
    }
}
