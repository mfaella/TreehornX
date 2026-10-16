struct Node {
    int data;
    struct Node *next;
};

void sll_post_set_zero(struct Node *root) {
    struct Node *curr;
    curr = root;
    while (curr) {
        curr->data = 0;
        curr = curr->next;
    }
}
