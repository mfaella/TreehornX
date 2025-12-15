struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_pop(struct Node **head) {
    struct Node *first;
    int result;

    first = *head;

    if(first) {
        free(first);
        result = first->data;
    }
}