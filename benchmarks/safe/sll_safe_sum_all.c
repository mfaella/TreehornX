struct Node {
    struct Node *next;
    int value;
};

void sll_safe_sum_all(struct Node ** head) {
    struct Node *current;
    int sum;
    int dif;
    int sumdif;
    int temp;

    current = *head;
    sum = 0;
    dif = 0;
    
    while(current != 0) {
        temp = current->value;
        sum = sum + temp;
        current = current->next;
    } 

    current = *head;
    while(current != 0) {
        temp = current->value;
        dif = dif - temp;
        current = current->next;
    }

    sumdif = sum + dif;
    if (sumdif != 0) {
        current->value = 0;
    }
}
