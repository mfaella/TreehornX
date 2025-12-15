struct Node {
    int value;
    struct Node *next;
};

void sll_safe_find(struct Node *root, int key) {
    struct Node *curr;
    struct Node *result;
    struct Node *null;
    int tmp_key;
    curr = root;

    while(curr) {
        tmp_key = curr->value;
        if(tmp_key == key) {
            result = curr;
            curr = null;
        }
        else {
            curr = curr->next;
        }
    }
}
