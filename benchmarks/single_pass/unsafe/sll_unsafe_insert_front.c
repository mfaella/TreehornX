struct Node {
    int value;
    struct Node *next;
};  

void sll_unsafe_insert_front(struct Node **head, int key) {
    struct Node *x;
    struct Node *z;
    struct Node *w;

    z = malloc(sizeof(struct Node));

    x = *head;
    z = z->next;
    z->value = key;
    z->next = x;
}