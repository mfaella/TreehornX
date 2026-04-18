struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_circular(struct Node *root) {
    struct Node *current;
    struct Node *tmp;

    if (!root) {
        return;
    }

    tmp = root;
    current = tmp->next;
    while(current) {
        tmp = current;
        current = current->next;
    }
    tmp->next = root;

}
